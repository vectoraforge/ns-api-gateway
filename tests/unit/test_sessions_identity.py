"""External IDP authentication and identity resolution, as `01-sessions-and-identity-resolution`
defines it: the ownership boundary, the per-request bearer contract, the three-way route
partition, the provider-callback category, the minimum JWT acceptance policy, and what an
acceptance failure does.
"""

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog
import yaml
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from nativespeaker.api.app.errors import register_exception_handlers
from nativespeaker.api.auth.audit import (
    AlertPolicyError,
    AuthEventResult,
    AuthResultCounter,
    InvalidExternalJwtAlerting,
    InvalidJwtAlertPolicy,
)
from nativespeaker.api.auth.barrier import (
    AuthBarrier,
    AuthBarrierMiddleware,
    VerifiedIdentityContext,
    extract_bearer_token,
)
from nativespeaker.api.auth.callbacks import (
    SUPPLEMENTARY_CONTROLS,
    CallbackRequest,
    ProviderCallbackConfigError,
    ProviderCallbackError,
    apple_signed_payload_verifier,
    assert_callback_configuration,
    callback_configuration_problems,
    configured_store_integrations,
    pubsub_oidc_verifier,
    registered_callback_routes,
    verify_provider_callback,
)
from nativespeaker.api.auth.external_identities import resolve_owner
from nativespeaker.api.auth.integration import (
    FirebaseIntegrations,
    UnrecognizedProviderError,
    build_firebase_integrations,
)
from nativespeaker.api.auth.operations import IdentityProvider
from nativespeaker.api.auth.profile import OrphanUserError
from nativespeaker.api.auth.routes import (
    AUTHENTICATED_ROUTES,
    PROVIDER_CALLBACK_ROUTES,
    PUBLIC_ROUTES,
    ProviderCallbackRoute,
    RouteCategory,
    RouteCategoryError,
    assert_route_categories,
    backend_credential_violations,
    categorize,
    named_verifier,
    registered_routes,
)
from nativespeaker.api.auth.tokens import (
    FirebaseIdTokenVerifier,
    InvalidExternalJwtError,
    JwtRejectionReason,
)
from nativespeaker.api.config import AppConfig, EnvironmentConfig
from nativespeaker.api.routers import build_webhooks_router
from unit.conftest import PUBLIC_KEY_PEM, TEST_ISSUER, TEST_PROJECT_ID, make_token
from unit.test_auth_barrier import (
    FakeResolver,
    RecordingSink,
    build_app,
    make_integrations,
    make_verifier,
    make_writer,
    subject_hasher,
)

TOKEN_HEADER = "Authorization"

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
SHIPPED_RAW_CONFIG = yaml.safe_load((CONFIG_DIR / "config.yaml").read_text())

# The values the shipped configuration file deliberately leaves to the deployment's environment
# rather than writing into the file: database credentials, the Firebase project, and Apple's root
# certificate directory.
DEPLOYMENT_ENVIRONMENT = {
    "DB_HOST": "db",
    "DB_PORT": "5432",
    "DB_USER": "nativespeaker",
    "DB_PASSWORD": "deployment-secret",
    "DB_NAME": "nativespeaker",
    "JWT_PROJECT_ID": "deployment-project",
    "JWT_API_KEY": "deployment-api-key",
    "AUTH_SUBJECT_HASH_KEY": "deployment-subject-hash-key",
    "APPLE_CERTS_DIR": "/etc/nativespeaker/apple-certs",
}


def shipped_app_config() -> AppConfig:
    """The shipped configuration as the running service resolves it: `config/config.yaml` plus
    the environment variables the deployment supplies for the keys the file leaves out."""
    with patch.dict(os.environ, DEPLOYMENT_ENVIRONMENT):
        config = EnvironmentConfig(config_dir=CONFIG_DIR).app_config
    assert config is not None
    return config


def shipped_app() -> FastAPI:
    from nativespeaker.api.app.main import app  # noqa: PLC0415

    return app


# Every provider-callback route, so the split proof runs on each of them rather than on whichever
# one happens to be convenient.
CALLBACK_ROUTE_CASES = [pytest.param(route, id=route.path) for route in PROVIDER_CALLBACK_ROUTES]

APPLE_SIGNED_PAYLOAD = "apple.signed.payload"


def _accepts_only_apples_jws(payload: str) -> None:
    """A stand-in for the backend's own verification of Apple's body JWS."""
    if payload != APPLE_SIGNED_PAYLOAD:
        raise ProviderCallbackError("the signedPayload is not one Apple signed")


def callback_verifiers(route: ProviderCallbackRoute) -> dict:
    """The one named verifier this route declares, and nothing else."""
    if route.verifier == "pubsub_oidc":
        return {"pubsub_oidc": pubsub_oidc_verifier(_accepts_only_pubsub_oidc)}
    return {"apple_signed_payload": apple_signed_payload_verifier(_accepts_only_apples_jws)}


def provider_credential_material(route: ProviderCallbackRoute) -> str:
    """The credential the calling store presents on this route."""
    return _pubsub_oidc_token() if route.verifier == "pubsub_oidc" else APPLE_SIGNED_PAYLOAD


def valid_credential(route: ProviderCallbackRoute) -> CallbackRequest:
    """The store's own credential, in the field that route carries it in: `Authorization` for
    Google's Pub/Sub push, the body JWS for Apple."""
    if route.verifier == "pubsub_oidc":
        return CallbackRequest(route.method, route.path,
                               authorization=(f"Bearer {_pubsub_oidc_token()}",))
    return CallbackRequest(route.method, route.path,
                           body={"signedPayload": APPLE_SIGNED_PAYLOAD})


def invalid_credential(route: ProviderCallbackRoute) -> CallbackRequest:
    if route.verifier == "pubsub_oidc":
        return CallbackRequest(route.method, route.path,
                               authorization=("Bearer not-an-oidc-token",))
    return CallbackRequest(route.method, route.path, body={"signedPayload": "not-apples-jws"})


def callback_app(path: str = "/webhooks/google-play/rtdn") -> FastAPI:
    """An app whose provider-callback route echoes what actually reached the handler, so the
    barrier's treatment of the request is visible from the response."""
    app = FastAPI()

    async def handler(request: Request):
        body = await request.body()
        return {"authorization": request.headers.getlist("authorization"),
                "body": body.decode(),
                "identity": getattr(request.state, "identity", None) is not None}

    app.add_api_route(path, handler, methods=["POST"])
    register_exception_handlers(app)
    app.add_middleware(AuthBarrierMiddleware)  # ty: ignore[invalid-argument-type]
    app.state.auth_barrier = AuthBarrier(integrations=make_integrations(),
                                         resolver=FakeResolver(),
                                         audit=make_writer(),
                                         subject_hasher=subject_hasher)
    return app


# --- Ownership boundary -------------------------------------------------------------------------


class TestOwnershipBoundary:
    # [utest->req~sessions-users-id-not-auth-key~1]
    def test_identity_resolution_never_runs_on_a_user_id(self):
        resolver = FakeResolver()
        app = build_app([("GET", "/users/me")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me",
                                  headers={TOKEN_HEADER: f"Bearer {make_token('u1')}"})
        # The only lookup key an authenticated request produces is the verified `(iss, sub)`.
        assert response.status_code == 200
        assert resolver.seen == [(TEST_ISSUER, "u1")]

    # [utest->req~sessions-users-id-not-auth-key~1]
    def test_a_user_row_without_an_identity_row_is_an_unresolvable_owner(self):
        # A path that arrives by user id — a support query, an attribution lookup — fails closed
        # as an internal error instead of inventing, reassigning or repairing an identity row.
        from uuid import uuid7
        user_id = uuid7()
        with pytest.raises(OrphanUserError) as orphan:
            resolve_owner(None, user_id=user_id)
        assert orphan.value.result is AuthEventResult.internal_error
        assert orphan.value.user_id == user_id


# --- Per-request external IDP token authentication ----------------------------------------------


class TestPerRequestAuthentication:
    # [utest->req~sessions-bearer-firebase-id-token~1]
    def test_an_authenticated_request_presents_the_id_token_as_a_bearer_credential(self):
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            token = make_token("u1")
            assert client.get("/users/me").status_code == 401
            assert client.get("/users/me",
                              headers={TOKEN_HEADER: f"Bearer {token}"}).status_code == 200

    # [utest->req~sessions-backend-sole-jwt-verifier~1]
    def test_the_backend_verifies_signature_issuer_audience_validity_and_subject(self):
        verifier = make_verifier()
        assert verifier.verify_id_token(make_token("u1")).subject == "u1"
        branches = [
            ("wrong signing key", make_token("u1", private_key=_other_private_key()),
             JwtRejectionReason.bad_signature),
            ("wrong issuer", make_token("u1", iss="https://securetoken.google.com/other"),
             JwtRejectionReason.issuer_mismatch),
            ("wrong audience", make_token("u1", aud="other-project"),
             JwtRejectionReason.audience_mismatch),
            ("expired", make_token("u1", exp=time.time() - 60, iat=time.time() - 120),
             JwtRejectionReason.expired),
            ("empty subject", make_token(""), JwtRejectionReason.empty_subject),
        ]
        for name, token, reason in branches:
            with pytest.raises(InvalidExternalJwtError) as exc:
                verifier.verify_id_token(token)
            assert exc.value.reason is reason, name
        # Claims are never read without verifying the signature.
        with pytest.raises(InvalidExternalJwtError):
            verifier.verify_id_token(make_token(algorithm="none", private_key=None))  # type: ignore[invalid-argument-type]

    # [utest->req~sessions-backend-sole-jwt-verifier~1]
    def test_a_request_costs_one_local_verification_and_no_network_call(self):
        resolutions: list[str] = []

        def key_resolver(token: str):
            resolutions.append(token)
            return PUBLIC_KEY_PEM

        verifier = FirebaseIdTokenVerifier(issuer=TEST_ISSUER, audience=TEST_PROJECT_ID,
                                           key_resolver=key_resolver)
        verifier.verify_id_token(make_token("u1"))
        assert len(resolutions) == 1

    # [utest->req~sessions-no-check-revoked~1]
    async def test_verification_makes_no_per_request_revocation_check(self):
        class ExplodingAdminClient:
            def __getattr__(self, name):
                raise AssertionError(f"the request path called Firebase Admin: {name}")

        integrations = FirebaseIntegrations(
            [type(make_integrations().sole)(issuer=TEST_ISSUER, project_id=TEST_PROJECT_ID,
                                            verifier=make_verifier(),
                                            admin_client=ExplodingAdminClient())])
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        app.state.auth_barrier = AuthBarrier(integrations=integrations, resolver=FakeResolver(),
                                             audit=make_writer(), subject_hasher=subject_hasher)
        with TestClient(app, raise_server_exceptions=False) as client:
            # A token minted an hour ago is still valid: nothing consults a revocation list, and
            # no Admin round-trip happens on the hot path at all.
            token = make_token("u1", iat=time.time() - 3600)
            assert client.get("/users/me",
                              headers={TOKEN_HEADER: f"Bearer {token}"}).status_code == 200

    # [utest->req~sessions-identity-from-verified-iss-sub~1]
    def test_identity_comes_from_the_verified_claims_and_from_nothing_else(self):
        resolver = FakeResolver(provider=IdentityProvider.google)
        app = build_app([("POST", "/auth/sync")], resolver=resolver, writer=make_writer())
        token = make_token("verified-subject",
                           extra_claims={"firebase": {"sign_in_provider": "apple"}})
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync?subject=spoofed",
                                   headers={TOKEN_HEADER: f"Bearer {token}",
                                            "X-Jwt-Claim-Sub": "spoofed",
                                            "X-Endpoint-Api-Userinfo": "spoofed",
                                            "Cookie": "subject=spoofed"},
                                   json={"subject": "spoofed"})
        assert resolver.seen == [(TEST_ISSUER, "verified-subject")]
        # The provider is the resolved identity's stored value, never the token's own claim.
        assert response.json()["provider"] == IdentityProvider.google


class TestAuthenticatedEndpointFamilies:
    # [utest->req~sessions-authenticated-endpoint-families~1]
    # [utest->req~sessions-authfamily-auth-sync~1]
    # [utest->req~sessions-authfamily-challenge-prepare~1]
    # [utest->req~sessions-authfamily-completion-calls~1]
    # [utest->req~sessions-authfamily-restore-subscription~1]
    # [utest->req~sessions-authfamily-users-me~1]
    # [utest->req~sessions-authfamily-chat-and-quota~1]
    # [utest->req~sessions-authfamily-sign-out-all~1]
    @pytest.mark.parametrize(("method", "path"), [
        ("POST", "/auth/sync"),
        ("POST", "/auth/create-user"),
        ("POST", "/auth/upgrade-anonymous"),
        ("POST", "/auth/claim-anonymous-grant"),
        ("POST", "/auth/claim-registered-grant"),
        ("POST", "/auth/restore-subscription"),
        ("GET", "/users/me"),
        ("GET", "/chats"),
        ("GET", "/users/me/quota"),
        ("POST", "/auth/sign-out-all"),
    ])
    def test_every_family_runs_through_the_one_shared_entry_point(self, method, path):
        assert categorize(method, path) is RouteCategory.authenticated
        app = build_app([(method, path)], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            unauthenticated = client.request(method, path)
            authenticated = client.request(
                method, path, headers={TOKEN_HEADER: f"Bearer {make_token('u1')}"})
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["code"] == "auth_required"
        assert authenticated.status_code == 200
        assert authenticated.json()["subject"] == "u1"


class TestSharedEntryPoint:
    # [utest->req~sessions-shared-entry-point-three-way-partition~1]
    def test_every_registered_route_is_in_exactly_one_of_the_three_categories(self):
        from nativespeaker.api.app.main import app

        categories = {path: categorize(method, path) for method, path in registered_routes(app)}
        assert categories, "the shipped app registers routes"
        assert set(categories.values()) <= {RouteCategory.public, RouteCategory.authenticated,
                                            RouteCategory.provider_callback}
        # Public means zero authentication, so the allowlist is exactly the probes. Equality, not
        # containment: widening it is how a route ends up served anonymously by accident.
        assert PUBLIC_ROUTES == frozenset({("GET", "/health/ready")})
        assert {path for path, category in categories.items()
                if category is RouteCategory.public} == {"/health/ready"}
        # The generated schema and documentation routes are not registered at all, so neither the
        # OpenAPI document nor Swagger UI is reachable without authentication.
        registered = {path for _, path in registered_routes(app)}
        assert not registered & {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

    # [utest->req~sessions-shared-entry-point-three-way-partition~1]
    def test_a_route_wired_outside_the_entry_point_fails_loudly(self):
        # Forgetting the wiring rejects as `auth_required`; it never leaves a silently open route.
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer(),
                        with_barrier=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me",
                                  headers={TOKEN_HEADER: f"Bearer {make_token('u1')}"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    # [utest->req~sessions-shared-entry-point-three-way-partition~1]
    def test_authentication_is_the_default_for_an_undeclared_route(self):
        assert categorize("GET", "/newly/added/route") is RouteCategory.authenticated

    # [utest->req~sessions-no-backend-tokens-or-session-tier~1]
    def test_no_route_mints_a_backend_token_and_no_context_carries_a_session(self):
        from dataclasses import fields

        from nativespeaker.api.app.main import app

        context_fields = [f.name for f in fields(VerifiedIdentityContext)]
        assert backend_credential_violations(registered_routes(app), context_fields) == []
        # A minted backend credential or a server-side session tier is caught wherever it appears.
        assert backend_credential_violations([("POST", "/auth/token")], context_fields)
        assert backend_credential_violations([("POST", "/auth/refresh")], context_fields)
        assert backend_credential_violations([], ["session_tier"])


class TestRouteEnumerationAssertion:
    # [utest->req~sessions-route-enumeration-assertion~1]
    def test_the_assertion_fails_closed_on_a_route_in_no_category(self):
        app = FastAPI()

        @app.get("/secret/backdoor")
        async def backdoor():
            return {}

        with pytest.raises(RouteCategoryError):
            assert_route_categories(app)

    # [utest->req~sessions-route-enumeration-assertion~1]
    def test_the_assertion_fails_closed_on_double_membership_and_generic_bypass(self, monkeypatch):
        monkeypatch.setattr("nativespeaker.api.auth.routes.PROVIDER_CALLBACK_ROUTES",
                            (ProviderCallbackRoute("POST", "/webhooks/app-store", "external"),))
        with pytest.raises(RouteCategoryError, match="named verifier"):
            assert_route_categories(FastAPI())
        monkeypatch.setattr("nativespeaker.api.auth.routes.PROVIDER_CALLBACK_ROUTES",
                            (ProviderCallbackRoute("GET", "/health/ready", "pubsub_oidc"),))
        with pytest.raises(RouteCategoryError, match="more than one category"):
            assert_route_categories(FastAPI())

    # The split is proved on *each* provider-callback route, not just on one of them: the four
    # cases below are parametrized over the whole registry.
    # [utest->req~sessions-route-enumeration-assertion~1]
    @pytest.mark.parametrize("route", CALLBACK_ROUTE_CASES)
    def test_a_callback_route_is_reachable_without_a_firebase_token(self, route):
        app = callback_app(route.path)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.request(route.method, route.path, json={"message": {}})
        assert response.status_code == 200
        # The barrier resolved no identity for it: it is not behind the user-token barrier.
        assert response.json()["identity"] is False

    # [utest->req~sessions-route-enumeration-assertion~1]
    @pytest.mark.parametrize("route", CALLBACK_ROUTE_CASES)
    async def test_a_callback_route_rejects_a_missing_or_invalid_provider_credential(self, route):
        verifiers = callback_verifiers(route)
        with pytest.raises(ProviderCallbackError):
            await verify_provider_callback(CallbackRequest(route.method, route.path), verifiers)
        with pytest.raises(ProviderCallbackError):
            await verify_provider_callback(invalid_credential(route), verifiers)
        # The route's own credential, presented where the route expects it, is what admits it.
        assert await verify_provider_callback(valid_credential(route), verifiers) == route.verifier

    # [utest->req~sessions-route-enumeration-assertion~1]
    @pytest.mark.parametrize("route", CALLBACK_ROUTE_CASES)
    async def test_a_firebase_user_token_never_stands_in_for_provider_verification(self, route):
        # A valid Firebase user token in the `Authorization` field, and none of the store's own
        # credential: refused by the named verifier on either route, Apple's included, whose
        # verifier reads the body JWS and never consults `Authorization` at all.
        firebase = CallbackRequest(route.method, route.path,
                                   authorization=(f"Bearer {make_token('u1')}",))
        with pytest.raises(ProviderCallbackError):
            await verify_provider_callback(firebase, callback_verifiers(route))

    # [utest->req~sessions-route-enumeration-assertion~1]
    @pytest.mark.parametrize("route", CALLBACK_ROUTE_CASES)
    def test_a_provider_credential_opens_no_route_behind_the_barrier(self, route):
        # The Pub/Sub OIDC token is issued by Google's account issuer for the push endpoint's
        # audience, and Apple's credential is a signed payload, not an ID token at all; the
        # barrier's Firebase acceptance policy refuses either as a bearer token.
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/users/me",
                headers={TOKEN_HEADER: f"Bearer {provider_credential_material(route)}"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"


# --- Provider-callback routes -------------------------------------------------------------------


class TestProviderCallbackRoutes:
    # [utest->req~sessions-provider-callback-third-category~1]
    def test_the_two_store_webhooks_are_neither_public_nor_behind_the_barrier(self):
        for route in PROVIDER_CALLBACK_ROUTES:
            assert categorize(route.method, route.path) is RouteCategory.provider_callback
            assert (route.method, route.path) not in PUBLIC_ROUTES
            assert (route.method, route.path) not in {(r.method, r.path)
                                                      for r in AUTHENTICATED_ROUTES}

    # [utest->req~sessions-provider-callback-membership-closed~1]
    def test_membership_is_closed_and_enumerated_by_exact_path(self):
        assert {(route.method, route.path) for route in PROVIDER_CALLBACK_ROUTES} == {
            ("POST", "/webhooks/app-store"),
            ("POST", "/webhooks/google-play/rtdn"),
        }

    # [utest->req~sessions-webhook-app-store-path~1]
    def test_the_app_store_notification_path(self):
        assert categorize("POST", "/webhooks/app-store") is RouteCategory.provider_callback
        assert named_verifier("POST", "/webhooks/app-store") == "apple_signed_payload"

    # [utest->req~sessions-webhook-google-play-rtdn-path~1]
    def test_the_play_rtdn_push_path(self):
        assert categorize("POST", "/webhooks/google-play/rtdn") is RouteCategory.provider_callback
        assert named_verifier("POST", "/webhooks/google-play/rtdn") == "pubsub_oidc"

    # [utest->req~sessions-no-wildcard-callback-membership~1]
    def test_a_path_prefix_confers_no_membership(self):
        for path in ("/webhooks/anything", "/webhooks/app-store/extra", "/webhooks/"):
            assert named_verifier("POST", path) is None
            assert categorize("POST", path) is RouteCategory.authenticated
        # A client posting purchase evidence stays a signed-in user on a barrier route.
        assert categorize("POST", "/auth/restore-subscription") is RouteCategory.authenticated

    # [utest->req~sessions-named-verifier-per-callback-route~1]
    def test_each_callback_route_declares_one_named_verifier(self):
        assert [route.verifier for route in PROVIDER_CALLBACK_ROUTES] == ["apple_signed_payload",
                                                                          "pubsub_oidc"]

    # [utest->req~sessions-named-verifier-per-callback-route~1]
    async def test_an_unnamed_or_missing_verifier_admits_nothing(self):
        request = CallbackRequest("POST", "/webhooks/app-store", body={"signedPayload": "jws"})
        with pytest.raises(ProviderCallbackError, match="not configured"):
            await verify_provider_callback(request, {})
        # A generic external bypass is not one of the named verifiers.
        with pytest.raises(ProviderCallbackError, match="not configured"):
            await verify_provider_callback(request, {"external": lambda _request: None})

    # [utest->req~sessions-named-verifier-per-callback-route~1]
    def test_an_unconfigured_store_registers_no_route_and_a_registered_one_needs_its_config(self):
        # A store's route is not registered at all while that store's integration is unconfigured.
        assert registered_callback_routes([]) == ()
        assert [route.path for route in registered_callback_routes(["apple"])] == [
            "/webhooks/app-store"]
        # A registered route whose named verifier lacks its configuration fails startup closed.
        registered = [("POST", "/webhooks/app-store")]
        with pytest.raises(ProviderCallbackConfigError, match="apple.bundle_id"):
            assert_callback_configuration(registered, {"apple": {"certs_dir": "/tmp"}}, {})
        assert_callback_configuration(registered, {"apple": {"bundle_id": "com.example",
                                                             "environment": "sandbox",
                                                             "certs_dir": "/tmp/certs"}}, {})

    # [utest->req~sessions-named-verifier-per-callback-route~1]
    def test_an_unconfigured_store_is_absent_from_the_routers_registered_routes(self):
        """The router itself is built from the filtered registry, so an unconfigured store's path
        is not in `app.routes` at all — not registered and then refused."""
        def callback_paths(raw_config: dict) -> list[tuple[str, str]]:
            router = build_webhooks_router(configured_store_integrations(raw_config))
            return sorted(registered_routes(router))

        assert callback_paths({"quotas": {}}) == []
        assert callback_paths({"apple": {"bundle_id": "x"}}) == [
            ("POST", "/webhooks/app-store")]
        # Google Play has no configuration section of its own, so its route is never registered.
        assert configured_store_integrations(SHIPPED_RAW_CONFIG) == ("apple",)

    # [utest->req~sessions-named-verifier-per-callback-route~1]
    def test_the_shipped_configuration_plus_its_environment_boots(self):
        """The startup gate resolves each verifier's required configuration against the validated
        settings, not the YAML file alone: `apple.certs_dir` is supplied as `APPLE_CERTS_DIR` and
        never appears in `config/config.yaml`, so checking the file alone would refuse to boot a
        correctly configured deployment."""
        assert "certs_dir" not in SHIPPED_RAW_CONFIG["apple"]
        resolved = shipped_app_config().model_dump()
        registered = registered_routes(shipped_app())

        assert_callback_configuration(registered, resolved, SHIPPED_RAW_CONFIG)
        # Judging the file alone is the boot-blocking false positive this guards against.
        assert callback_configuration_problems(registered, {}, SHIPPED_RAW_CONFIG) == [
            "/webhooks/app-store is registered without apple.certs_dir"]
        # And the check is still a real one: blank the resolved value and it fails closed again.
        blank = dict(resolved, apple=dict(resolved["apple"], certs_dir=None))
        with pytest.raises(ProviderCallbackConfigError, match="apple.certs_dir"):
            assert_callback_configuration(registered, blank, SHIPPED_RAW_CONFIG)

    # [utest->req~sessions-gateway-behavior-callback-paths-only~1]
    def test_callback_treatment_applies_to_those_two_paths_and_no_others(self):
        from nativespeaker.api.app.main import app

        callbacks = {(route.method, route.path) for route in PROVIDER_CALLBACK_ROUTES}
        for method, path in registered_routes(app):
            category = categorize(method, path)
            assert (category is RouteCategory.provider_callback) == ((method, path) in callbacks)

    # [utest->req~sessions-gateway-forwards-pubsub-oidc-unchanged~1]
    def test_the_rtdn_authorization_field_reaches_the_handler_unchanged(self):
        token = _pubsub_oidc_token()
        app = callback_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/webhooks/google-play/rtdn",
                                   headers={TOKEN_HEADER: f"Bearer {token}"},
                                   json={"message": {}})
        # The barrier neither verifies nor strips it: the backend's own OIDC verification does.
        assert response.status_code == 200
        assert response.json()["authorization"] == [f"Bearer {token}"]

    # [utest->req~sessions-gateway-forwards-pubsub-oidc-unchanged~1]
    async def test_the_backend_performs_the_oidc_verification_itself(self):
        seen: list[str] = []

        def verify(token: str) -> None:
            seen.append(token)
            _accepts_only_pubsub_oidc(token)

        token = _pubsub_oidc_token()
        name = await verify_provider_callback(
            CallbackRequest("POST", "/webhooks/google-play/rtdn",
                            authorization=(f"Bearer {token}",)),
            {"pubsub_oidc": pubsub_oidc_verifier(verify)})
        assert name == "pubsub_oidc"
        assert seen == [token]

    # [utest->req~sessions-gateway-never-parses-apple-signedpayload~1]
    async def test_apples_credential_is_the_body_jws_and_needs_no_authorization_field(self):
        verified: list[str] = []
        request = CallbackRequest("POST", "/webhooks/app-store",
                                  body={"signedPayload": "apple.jws.payload"})
        assert request.authorization == ()
        await verify_provider_callback(
            request, {"apple_signed_payload": apple_signed_payload_verifier(verified.append)})
        assert verified == ["apple.jws.payload"]
        # No JWS in the body is nothing to verify, so the call is not admitted.
        with pytest.raises(ProviderCallbackError):
            await verify_provider_callback(
                CallbackRequest("POST", "/webhooks/app-store", body={}),
                {"apple_signed_payload": apple_signed_payload_verifier(verified.append)})

    # [utest->req~sessions-gateway-edge-role-only-on-callbacks~1]
    async def test_edge_rate_limiting_never_substitutes_for_the_backend_verification(self):
        # However generously a callback request is admitted at the edge, it reaches the backend
        # still owing its provider credential, and the named verifier is what admits it.
        rate_limited_but_unverified = CallbackRequest("POST", "/webhooks/google-play/rtdn")
        with pytest.raises(ProviderCallbackError):
            await verify_provider_callback(
                rate_limited_but_unverified,
                {"pubsub_oidc": pubsub_oidc_verifier(_accepts_only_pubsub_oidc)})

    # [utest->req~sessions-no-supplementary-callback-controls~1]
    def test_a_supplementary_control_on_a_callback_route_is_a_startup_error(self):
        base = {"bundle_id": "com.example", "environment": "sandbox", "certs_dir": "/tmp/certs"}
        registered = [("POST", "/webhooks/app-store")]
        assert callback_configuration_problems(registered, {"apple": base},
                                               {"apple": base}) == []
        for control in ("secret_url_token", "ip_allowlist", "mtls", "certificate_pinning"):
            # Read from the file as written: validation would silently drop a forbidden key, so a
            # supplementary control has to be caught where it was written.
            problems = callback_configuration_problems(
                registered, {"apple": base}, {"apple": {**base, control: "on"}})
            assert any(control in problem for problem in problems), control
        assert {"secret_url_token", "ip_allowlist", "mtls"} <= SUPPLEMENTARY_CONTROLS


# --- Minimum external JWT acceptance ------------------------------------------------------------


class TestWireContract:
    # [utest->req~sessions-wire-authorization-bearer-sole-carrier~1]
    def test_the_authorization_field_is_the_sole_identity_carrier(self):
        resolver = FakeResolver()
        app = build_app([("POST", "/auth/sync")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={TOKEN_HEADER: f"Bearer {make_token('real')}"})
        assert response.status_code == 200
        assert resolver.seen == [(TEST_ISSUER, "real")]

    # [utest->req~sessions-wire-exactly-one-credential~1]
    def test_exactly_one_well_formed_credential_and_nothing_else(self):
        token = make_token("u1")
        assert extract_bearer_token([f"Bearer {token}"]) == token
        rejected = {
            "zero fields": ([], JwtRejectionReason.missing_token),
            "two fields": ([f"Bearer {token}", f"Bearer {token}"],
                           JwtRejectionReason.duplicate_authorization),
            "comma-joined": ([f"Bearer {token}, Bearer {token}"],
                             JwtRejectionReason.duplicate_authorization),
            "folded": ([f"Bearer {token}\r\n Bearer {token}"],
                       JwtRejectionReason.duplicate_authorization),
            "empty token": (["Bearer "], JwtRejectionReason.missing_token),
            "empty value": ([""], JwtRejectionReason.malformed),
            "trailing content": ([f"Bearer {token} extra"], JwtRejectionReason.malformed),
            "two credentials": ([f"Bearer {token} {token}"], JwtRejectionReason.malformed),
        }
        for name, (values, reason) in rejected.items():
            with pytest.raises(InvalidExternalJwtError) as exc:
                extract_bearer_token(values)
            assert exc.value.reason is reason, name

    # [utest->req~sessions-wire-case-insensitive-duplicate-fields~1]
    def test_differently_cased_field_names_are_the_same_field_and_count_as_duplicates(self):
        token = make_token("u1")
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me",
                                  headers=[("Authorization", f"Bearer {token}"),
                                           ("authorization", f"Bearer {make_token('other')}")])
        # Rejected before any value is picked, so no two components can authenticate different
        # credentials out of one request.
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    # [utest->req~sessions-wire-claims-from-verifying-decode~1]
    def test_issuer_and_subject_are_exactly_the_verified_claims(self):
        claims = make_verifier().verify_id_token(make_token("subject-1"))
        assert (claims.issuer, claims.subject) == (TEST_ISSUER, "subject-1")
        # Nothing is reconstructed from transport metadata: a token the verifier rejects yields
        # no claims at all.
        with pytest.raises(InvalidExternalJwtError):
            make_verifier().verify_id_token(make_token("subject-1",
                                                       private_key=_other_private_key()))

    # [utest->req~sessions-wire-no-alternate-token-location~1]
    def test_a_token_is_never_accepted_from_any_other_location(self):
        token = make_token("u1")
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            attempts = [
                client.get(f"/users/me?access_token={token}"),
                client.get("/users/me", headers={"Cookie": f"id_token={token}"}),
                client.get("/users/me", headers={"X-Authorization": f"Bearer {token}"}),
                client.get("/users/me", headers={"X-Forwarded-Authorization": f"Bearer {token}"}),
                client.get("/users/me", headers={"X-Endpoint-Api-Userinfo": token}),
            ]
        for response in attempts:
            assert response.status_code == 401
            assert response.json()["code"] == "auth_required"

    # [utest->req~sessions-wire-no-provider-derivation~1]
    def test_no_provider_or_account_class_is_derived_from_the_wire(self):
        resolver = FakeResolver(provider=None)
        app = build_app([("POST", "/auth/sync")], resolver=resolver, writer=make_writer())
        token = make_token("u1", extra_claims={"provider": "apple",
                                               "firebase": {"sign_in_provider": "apple"}})
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={TOKEN_HEADER: f"Bearer {token}",
                                            "X-Provider": "apple"})
        # The wire contract yields identity only; the provider stays whatever the resolved
        # identity says it is, which here is nothing.
        assert response.json()["provider"] is None


class TestDivisionOfResponsibility:
    # [utest->req~sessions-backend-authoritative-verifier~1]
    def test_the_backend_verifies_every_request_itself(self):
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            # A header claiming the edge already verified the request changes nothing.
            response = client.get("/users/me",
                                  headers={"X-Jwt-Verified": "true",
                                           "X-Envoy-Jwt-Payload": "verified"})
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    # [utest->req~sessions-backend-ignores-identity-headers~1]
    def test_identity_headers_are_ignored_for_authentication(self):
        resolver = FakeResolver()
        app = build_app([("GET", "/users/me")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me",
                                  headers={TOKEN_HEADER: f"Bearer {make_token('real')}",
                                           "X-Forwarded-User": "spoofed",
                                           "X-Goog-Authenticated-User-Id": "spoofed"})
        assert response.status_code == 200
        assert resolver.seen == [(TEST_ISSUER, "real")]

    # [utest->req~sessions-no-second-backend-header-check~1]
    def test_no_second_check_compares_a_header_with_the_token(self):
        # A header that agrees with the token and one that contradicts it produce the same
        # outcome: there is no dual read and no equality check between them.
        def call(headers):
            resolver = FakeResolver()
            app = build_app([("GET", "/users/me")], resolver=resolver, writer=make_writer())
            with TestClient(app, raise_server_exceptions=False) as client:
                return client.get("/users/me", headers=headers), resolver.seen

        token = make_token("real")
        agreeing, agreeing_seen = call({TOKEN_HEADER: f"Bearer {token}", "X-User-Id": "real"})
        contradicting, contradicting_seen = call({TOKEN_HEADER: f"Bearer {token}",
                                                  "X-User-Id": "someone-else"})
        assert agreeing.status_code == contradicting.status_code == 200
        assert agreeing.json() == contradicting.json()
        assert agreeing_seen == contradicting_seen == [(TEST_ISSUER, "real")]

    # [utest->req~sessions-gateway-backend-same-project-pin~1]
    def test_one_project_pins_the_issuer_and_the_audience(self):
        integrations = build_firebase_integrations(issuer=TEST_ISSUER,
                                                   project_id=TEST_PROJECT_ID,
                                                   jwks_url="https://example.invalid/jwks",
                                                   admin_client=object(),
                                                   warm=False)
        assert integrations.sole.issuer == f"https://securetoken.google.com/{TEST_PROJECT_ID}"
        assert integrations.sole.project_id == TEST_PROJECT_ID
        # A token from another Firebase project matches neither.
        for token in (make_token("u1", iss="https://securetoken.google.com/other-project"),
                      make_token("u1", aud="other-project")):
            with pytest.raises(InvalidExternalJwtError):
                make_verifier().verify_id_token(token)


class TestRequiredBackendRules:
    # [utest->req~sessions-jwt-acceptance-policy-scope~1]
    def test_verification_runs_in_the_barrier_ahead_of_identity_resolution(self):
        resolver = FakeResolver()
        app = build_app([("GET", "/users/me")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            rejected = client.get("/users/me", headers={TOKEN_HEADER: "Bearer nonsense"})
            admitted = client.get("/users/me",
                                  headers={TOKEN_HEADER: f"Bearer {make_token('u1')}"})
        # A token that fails acceptance never reaches identity resolution, and the handler never
        # repeats the verification the barrier already did.
        assert rejected.status_code == 401
        assert resolver.seen == [(TEST_ISSUER, "u1")]
        assert admitted.json()["verified_by"] == "AuthBarrier"

    # [utest->req~sessions-lookup-keyed-on-issuer-subject~1]
    def test_the_lookup_key_is_the_verified_issuer_and_subject(self):
        resolver = FakeResolver()
        app = build_app([("POST", "/auth/sync")], resolver=resolver, writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/auth/sync", headers={TOKEN_HEADER: f"Bearer {make_token('u-42')}"})
        assert resolver.seen == [(TEST_ISSUER, "u-42")]

    # [utest->req~sessions-iss-must-equal-configured-issuer~1]
    def test_any_other_issuer_is_an_acceptance_failure(self):
        for issuer in ("https://securetoken.google.com/other",
                       "https://accounts.google.com",
                       f"{TEST_ISSUER}/",
                       TEST_ISSUER.upper()):
            with pytest.raises(InvalidExternalJwtError) as exc:
                make_verifier().verify_id_token(make_token("u1", iss=issuer))
            assert exc.value.reason is JwtRejectionReason.issuer_mismatch, issuer

    # [utest->req~sessions-any-verification-failure-rejects~1]
    @pytest.mark.parametrize("header", [
        None,
        "",
        "Bearer",
        "Basic dXNlcjpwYXNz",
        "Bearer not-a-jwt",
    ])
    def test_every_verification_failure_rejects_the_request(self, header):
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        headers = {} if header is None else {TOKEN_HEADER: header}
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/users/me", headers=headers)
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"

    # [utest->req~sessions-provider-only-from-providerdata~1]
    def test_the_provider_comes_only_from_the_admin_provider_data_lookup(self):
        class Entry:
            def __init__(self, provider_id):
                self.provider_id = provider_id

        assert FirebaseIntegrations.classify_provider([]) == "anonymous"
        assert FirebaseIntegrations.classify_provider([Entry("google.com")]) == "google"
        assert FirebaseIntegrations.classify_provider([Entry("apple.com")]) == "apple"
        # Anything else, however plausible a header or a claim made it look, is refused.
        for shape in ([Entry("facebook.com")], [Entry("password")], [Entry(None)]):
            with pytest.raises(UnrecognizedProviderError):
                FirebaseIntegrations.classify_provider(shape)


# --- External-JWT acceptance failures -----------------------------------------------------------


def _failure_headers() -> dict[str, dict[str, str]]:
    return {
        "missing": {},
        "malformed": {TOKEN_HEADER: "Basic abc"},
        "bad signature": {TOKEN_HEADER:
                          f"Bearer {make_token('u1', private_key=_other_private_key())}"},
        "wrong issuer": {TOKEN_HEADER:
                         f"Bearer {make_token('u1', iss='https://securetoken.google.com/x')}"},
        "wrong audience": {TOKEN_HEADER: f"Bearer {make_token('u1', aud='other')}"},
        "expired": {TOKEN_HEADER: f"Bearer {make_token('u1', exp=time.time() - 60)}"},
        "empty subject": {TOKEN_HEADER: f"Bearer {make_token('')}"},
    }


class TestAcceptanceFailures:
    # [utest->req~sessions-acceptance-failures-single-contract~1]
    def test_every_branch_audits_invalid_external_jwt_and_surfaces_auth_required(self):
        for name, headers in _failure_headers().items():
            sink = RecordingSink()
            app = build_app([("POST", "/auth/sync")], resolver=FakeResolver(),
                            writer=make_writer(sink=sink))
            with TestClient(app, raise_server_exceptions=False) as client:
                response = client.post("/auth/sync", headers=headers)
            assert response.status_code == 401, name
            assert response.json()["code"] == "auth_required", name
            assert [row["result"] for row in sink.rows] == [
                AuthEventResult.invalid_external_jwt], name

    # [utest->req~sessions-acceptance-failure-response-indistinguishable~1]
    def test_the_client_response_is_identical_across_the_branches(self):
        responses = []
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(), writer=make_writer())
        with TestClient(app, raise_server_exceptions=False) as client:
            for headers in _failure_headers().values():
                responses.append(client.get("/users/me", headers=headers))
        bodies = {response.text for response in responses}
        statuses = {response.status_code for response in responses}
        assert statuses == {401}
        assert len(bodies) == 1
        # It names no issuer, no integration and no failed check.
        body = bodies.pop()
        for leak in ("securetoken", "issuer", "audience", "signature", "expired", TEST_PROJECT_ID):
            assert leak not in body

    # [utest->req~sessions-acceptance-failure-internal-reason~1]
    def test_the_bounded_reason_lives_only_in_audit_detail_and_metric_labels(self):
        sink = RecordingSink()
        counter = AuthResultCounter()
        app = build_app([("POST", "/auth/sync")], resolver=FakeResolver(),
                        writer=make_writer(sink=sink, counter=counter))
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/sync",
                                   headers={TOKEN_HEADER: f"Bearer {make_token('u1', aud='x')}"})
        assert sink.rows[0]["details"]["failure"]["reason"] == "audience_mismatch"
        assert counter.value(result=AuthEventResult.invalid_external_jwt,
                             route="/auth/sync", reason="audience_mismatch") == 1
        assert "audience_mismatch" not in response.text
        assert set(JwtRejectionReason) >= {JwtRejectionReason.missing_token,
                                           JwtRejectionReason.malformed,
                                           JwtRejectionReason.bad_signature,
                                           JwtRejectionReason.expired,
                                           JwtRejectionReason.audience_mismatch,
                                           JwtRejectionReason.issuer_mismatch}

    # [utest->req~sessions-acceptance-failure-durable-record-by-route~1]
    def test_where_the_rejection_is_recorded_depends_on_the_route_alone(self):
        # A canonical state-changing auth operation: its own row, with NULL actor fields.
        sink = RecordingSink()
        counter = AuthResultCounter()
        on_path = build_app([("POST", "/auth/sync")], resolver=FakeResolver(),
                            writer=make_writer(sink=sink, counter=counter))
        with TestClient(on_path, raise_server_exceptions=False) as client:
            client.post("/auth/sync", headers={TOKEN_HEADER: "Bearer nonsense"})
        assert [row["result"] for row in sink.rows] == [AuthEventResult.invalid_external_jwt]
        assert sink.rows[0]["actor_issuer"] is None
        assert sink.rows[0]["actor_subject_hash"] is None

        # Every other authenticated route: no row, and the named result code stays queryable in
        # the structured security log and in the counter.
        off_sink = RecordingSink()
        off_counter = AuthResultCounter()
        off_path = build_app([("GET", "/users/me")], resolver=FakeResolver(),
                             writer=make_writer(sink=off_sink, counter=off_counter))
        with structlog.testing.capture_logs() as logs:
            with TestClient(off_path, raise_server_exceptions=False) as client:
                client.get("/users/me", headers={TOKEN_HEADER: "Bearer nonsense"})
        assert off_sink.rows == []
        assert any(entry.get("result") == AuthEventResult.invalid_external_jwt for entry in logs)
        assert off_counter.value(result=AuthEventResult.invalid_external_jwt,
                                 route="/users/me", reason="malformed") == 1


class TestInvalidExternalJwtAlerting:
    # [utest->req~sessions-invalid-external-jwt-metric-alert~1]
    def test_the_counter_is_labeled_by_bounded_reason_and_route(self):
        counter = AuthResultCounter()
        app = build_app([("GET", "/chats/{chat_id}")], resolver=FakeResolver(),
                        writer=make_writer(counter=counter))
        with TestClient(app, raise_server_exceptions=False) as client:
            client.get("/chats/abc", headers={TOKEN_HEADER: "Bearer nonsense"})
        assert counter.labels() == [("invalid_external_jwt", "malformed", "/chats/{chat_id}")]

    # [utest->req~sessions-invalid-external-jwt-metric-alert~1]
    def test_baseline_noise_raises_no_alert_and_a_sustained_rise_does(self):
        clock = _FakeClock()
        alerting = InvalidExternalJwtAlerting(
            InvalidJwtAlertPolicy(window_seconds=60, threshold_count=5, sustained_windows=2),
            clock=clock)
        counter = AuthResultCounter(alerting)
        # Baseline: a couple of expired sessions per window, for several windows.
        for _ in range(6):
            for _ in range(2):
                counter.increment(result=AuthEventResult.invalid_external_jwt,
                                  route="/users/me", reason="expired")
            clock.advance(60)
        counter.increment(result=AuthEventResult.invalid_external_jwt, route="/users/me",
                          reason="expired")
        assert alerting.alerts == []

        # A rise that lasts more than one window raises the operational alert, once.
        for _ in range(3):
            for _ in range(9):
                counter.increment(result=AuthEventResult.invalid_external_jwt,
                                  route="/users/me", reason="bad_signature")
            clock.advance(60)
        counter.increment(result=AuthEventResult.invalid_external_jwt, route="/users/me",
                          reason="bad_signature")
        assert len(alerting.alerts) == 1
        assert alerting.alerts[0].reasons == ("bad_signature",)
        assert alerting.alerts[0].routes == ("/users/me",)

    # [utest->req~sessions-invalid-external-jwt-metric-alert~1]
    def test_the_threshold_may_be_a_fraction_of_authenticated_traffic(self):
        clock = _FakeClock()
        alerting = InvalidExternalJwtAlerting(
            InvalidJwtAlertPolicy(window_seconds=60, threshold_fraction=0.5, sustained_windows=1),
            clock=clock)
        counter = AuthResultCounter(alerting)
        for _ in range(10):
            counter.observe_authenticated_request()
        for _ in range(2):
            counter.increment(result=AuthEventResult.invalid_external_jwt, route="/chats",
                              reason="expired")
        clock.advance(60)
        counter.observe_authenticated_request()
        assert alerting.alerts == []
        for _ in range(4):
            counter.observe_authenticated_request()
            counter.increment(result=AuthEventResult.invalid_external_jwt, route="/chats",
                              reason="expired")
        clock.advance(60)
        counter.observe_authenticated_request()
        assert len(alerting.alerts) == 1

    # [utest->req~sessions-invalid-external-jwt-metric-alert~1]
    def test_a_threshold_is_configuration_and_must_be_one_of_the_two_forms(self):
        # The threshold is deployment configuration, carried by the shipped config model.
        from nativespeaker.api.config import AuthConfig
        configured = AuthConfig.model_validate({"subject_hash_key": "k",
                                               "invalid_external_jwt_alert": {
                                                   "window_seconds": 60,
                                                   "threshold_count": 25}})
        assert configured.invalid_external_jwt_alert.threshold_count == 25
        assert AuthConfig.model_validate(
            {"subject_hash_key": "k"}).invalid_external_jwt_alert.threshold_fraction
        with pytest.raises(AlertPolicyError):
            InvalidJwtAlertPolicy()
        with pytest.raises(AlertPolicyError):
            InvalidJwtAlertPolicy(threshold_count=5, threshold_fraction=0.5)
        with pytest.raises(AlertPolicyError):
            InvalidJwtAlertPolicy(threshold_fraction=1.5)
        assert InvalidJwtAlertPolicy(threshold_count=5).threshold_fraction is None

    # [utest->req~sessions-systemic-break-detection-path~1]
    def test_a_systemic_break_is_client_indistinguishable_and_only_the_alert_sees_it(self):
        clock = _FakeClock()
        alerting = InvalidExternalJwtAlerting(
            InvalidJwtAlertPolicy(window_seconds=60, threshold_count=3, sustained_windows=2),
            clock=clock)
        counter = AuthResultCounter(alerting)

        def unreachable_key_source(_token):
            raise ConnectionError("securetoken key set unreachable")

        integrations = FirebaseIntegrations(
            [type(make_integrations().sole)(
                issuer=TEST_ISSUER, project_id=TEST_PROJECT_ID,
                verifier=FirebaseIdTokenVerifier(issuer=TEST_ISSUER, audience=TEST_PROJECT_ID,
                                                 key_resolver=unreachable_key_source),
                admin_client=object())])
        app = build_app([("GET", "/users/me")], resolver=FakeResolver(),
                        writer=make_writer(counter=counter))
        app.state.auth_barrier = AuthBarrier(integrations=integrations, resolver=FakeResolver(),
                                             audit=make_writer(counter=counter),
                                             subject_hasher=subject_hasher)
        with TestClient(app, raise_server_exceptions=False) as client:
            for _window in range(3):
                for _ in range(4):
                    response = client.get(
                        "/users/me", headers={TOKEN_HEADER: f"Bearer {make_token('u1')}"})
                    # Every request fails exactly the way an ordinary session expiry does.
                    assert response.status_code == 401
                    assert response.json()["code"] == "auth_required"
                clock.advance(60)
        # Only the alert distinguishes the systemic break from that expected baseline.
        assert len(alerting.alerts) == 1
        assert alerting.alerts[0].reasons == ("signing_key_unavailable",)


# --- Helpers ------------------------------------------------------------------------------------


class _FakeClock:
    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _other_private_key() -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(encoding=serialization.Encoding.PEM,
                             format=serialization.PrivateFormat.PKCS8,
                             encryption_algorithm=serialization.NoEncryption())


PUBSUB_AUDIENCE = "https://api.example.com/webhooks/google-play/rtdn"
PUBSUB_SERVICE_ACCOUNT = "play-rtdn@example.iam.gserviceaccount.com"


def _pubsub_oidc_token() -> str:
    """The Pub/Sub push subscription's OIDC token: Google's account issuer, the push endpoint's
    audience, and the configured service account as its verified email."""
    return make_token("pubsub", iss="https://accounts.google.com", aud=PUBSUB_AUDIENCE,
                      extra_claims={"email": PUBSUB_SERVICE_ACCOUNT, "email_verified": True})


def _accepts_only_pubsub_oidc(token: str) -> None:
    """A stand-in for the backend's own Pub/Sub OIDC verification: Google's issuer, the push
    endpoint audience, and the configured service account."""
    import jwt as pyjwt

    try:
        claims = pyjwt.decode(token, PUBLIC_KEY_PEM, algorithms=["RS256"],
                              audience=PUBSUB_AUDIENCE, issuer="https://accounts.google.com")
    except pyjwt.PyJWTError as exc:
        raise ProviderCallbackError(f"the Pub/Sub OIDC token is not acceptable: {exc}") from None
    if claims.get("email") != PUBSUB_SERVICE_ACCOUNT or not claims.get("email_verified"):
        raise ProviderCallbackError("unexpected Pub/Sub service account")
