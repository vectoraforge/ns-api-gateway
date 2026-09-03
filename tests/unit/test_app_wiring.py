"""App-construction invariants admission depends on, asserted over the real app because runtime hides them."""
import pytest
from fastapi import Depends
from fastapi.routing import APIRoute

from nativespeaker.api.app.dependencies import get_identity, get_linked_identity
from nativespeaker.api.app.main import app as real_app

DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}


def _api_routes() -> list[APIRoute]:
    return [route for route in real_app.routes if isinstance(route, APIRoute)]


def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]


class TestEveryRouteIsAuthenticated:
    """The structural replacement for the deleted startup assertion: the declaration is what serves traffic."""

    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"

    def test_the_preauth_callable_route_still_resolves_the_identity(self):
        """Create-user is exempt from the narrowing, not from authentication: a linked caller is owed a 409."""
        for route in _api_routes():
            if route.path in PREAUTH_CALLABLE_PATHS:
                assert get_identity in _declared(route), route.path

    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant", "/users/me"))
    def test_a_narrowed_route_declares_the_linked_identity_narrowing(self, path):
        """Named rather than left to the generic case, which would also pass if the route were exempted."""
        declared = [_declared(route) for route in _api_routes() if route.path == path]
        assert declared, f"{path} is not a registered route"
        assert all(get_linked_identity in calls for calls in declared)

    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant", "/users/me"))
    def test_a_narrowed_route_is_in_neither_exemption_set(self, path):
        """The route is authenticated and narrowed, so widening either literal above would fail here."""
        assert path in {route.path for route in _api_routes()}
        assert path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS

    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        """A second public route would have to be added to `PUBLIC_PATHS` above to pass."""
        unauthenticated = {route.path for route in _api_routes()
                           if get_linked_identity not in _declared(route)
                           and get_identity not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS

    def test_no_route_declares_a_wrapper_around_an_accessor(self):
        """The cache keys on the callable, so a `wraps` wrapper would key differently and verify twice."""
        for route in _api_routes():
            for call in _declared(route):
                wrapped = getattr(call, "__wrapped__", None)
                assert wrapped not in (get_linked_identity, get_identity), \
                    f"{route.path} declares a wrapper around {getattr(wrapped, '__name__', wrapped)}"


class TestDocumentationRoutes:
    """No unauthenticated schema dump; these are registered on `app.router`, so they carry no router dependency."""

    def test_no_documentation_route_is_registered(self):
        registered_paths = {r.path for r in real_app.routes}
        assert registered_paths & DOC_PATHS == set()

    def test_openapi_is_still_generatable_as_a_method_call(self):
        """openapi_url=None removes the route, not the schema -- tests still introspect it."""
        assert "ErrorResponse" in real_app.openapi()["components"]["schemas"]


class TestRedirectSlashes:
    """The trailing-slash 307 is produced before any route's dependencies run."""

    def test_redirect_slashes_is_disabled(self):
        assert real_app.router.redirect_slashes is False


class TestTheAuthDependencyIsResolvedOncePerRequest:
    """One verify and one identity query, counted across both declaration levels and the context beneath."""

    def test_one_verify_and_one_query_for_a_doubly_declared_route(self):
        from uuid import uuid7

        from fastapi import APIRouter, FastAPI
        from fastapi.testclient import TestClient

        from nativespeaker.api.app.error_handlers import register_exception_handlers
        from nativespeaker.api.schemas.auth import Identity
        from nativespeaker.api.tables.identities import (
            ExternalIdentity,
            IdentityProvider,
            IdentityState,
        )
        from nativespeaker.api.tables.users import User
        from unit.conftest import TEST_ISSUER, make_test_verifier, make_token

        subject = "cache-contract-subject"
        counts = {"verify": 0, "query": 0}

        user = User(id=uuid7(), active=True)
        identity = ExternalIdentity(id=uuid7(), user_id=user.id, issuer=TEST_ISSUER,
                                    subject=subject, provider=IdentityProvider.google,
                                    provider_uid="g-1", identity_state=IdentityState.active)

        class _Result:
            def first(self):
                return identity, user

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_exc):
                return False

            async def exec(self, _statement):
                counts["query"] += 1
                return _Result()

        class _CountingVerifier:
            def __init__(self):
                self._inner = make_test_verifier()

            def verify(self, token):
                counts["verify"] += 1
                return self._inner.verify(token)

        app = FastAPI()
        register_exception_handlers(app)
        router = APIRouter(dependencies=[Depends(get_linked_identity)])

        @router.get("/chats/{chat_id}")
        async def _handler(chat_id: str,
                           who: Identity = Depends(get_linked_identity),
                           admitted: Identity = Depends(get_identity)):
            return {"same": who is admitted, "user": str(who.user.id)}

        app.include_router(router)
        app.state.jwt_verifier = _CountingVerifier()
        app.state.session_factory = _Session

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/chats/0199a0d0-0000-7000-8000-000000000000",
                              headers={"Authorization": f"Bearer {make_token(sub=subject)}"})

        assert response.status_code == 200, response.json()
        assert counts["verify"] == 1, f"the JWT was verified {counts['verify']} times"
        assert counts["query"] == 1, f"identity was resolved {counts['query']} times"
        # Both declarations received the one cached object, not two equal resolutions.
        assert response.json()["same"] is True
