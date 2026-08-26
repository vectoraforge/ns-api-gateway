"""App-construction invariants admission depends on, asserted over the real app because runtime hides them."""
from fastapi import Depends
from fastapi.routing import APIRoute

from nativespeaker.api.app.dependencies import get_linked_identity, get_request_context
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

    def test_the_preauth_callable_route_still_resolves_the_context(self):
        """Create-user is exempt from the narrowing, not from authentication: a linked caller is owed a 409."""
        for route in _api_routes():
            if route.path in PREAUTH_CALLABLE_PATHS:
                assert get_request_context in _declared(route), route.path

    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        """A second public route would have to be added to `PUBLIC_PATHS` above to pass."""
        unauthenticated = {route.path for route in _api_routes()
                           if get_linked_identity not in _declared(route)
                           and get_request_context not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS

    def test_no_route_declares_a_wrapper_around_an_accessor(self):
        """The cache keys on the callable, so a `wraps` wrapper would key differently and verify twice."""
        for route in _api_routes():
            for call in _declared(route):
                wrapped = getattr(call, "__wrapped__", None)
                assert wrapped not in (get_linked_identity, get_request_context), \
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

        from nativespeaker.api.app.errors import register_exception_handlers
        from nativespeaker.api.auth.context import LinkedIdentity, RequestContext
        from nativespeaker.api.models.identities import (
            ExternalIdentity,
            IdentityProvider,
            IdentityState,
        )
        from nativespeaker.api.models.users import User
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
                           who: LinkedIdentity = Depends(get_linked_identity),
                           context: RequestContext = Depends(get_request_context)):
            return {"route": context.route, "user": str(who.user.id)}

        app.include_router(router)
        app.state.jwt_verifier = _CountingVerifier()
        app.state.session_factory = _Session

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/chats/0199a0d0-0000-7000-8000-000000000000",
                              headers={"Authorization": f"Bearer {make_token(sub=subject)}"})

        assert response.status_code == 200, response.json()
        assert counts["verify"] == 1, f"the JWT was verified {counts['verify']} times"
        assert counts["query"] == 1, f"identity was resolved {counts['query']} times"
        # And the context carries the declared template, not the concrete id the caller sent.
        assert response.json()["route"] == "/chats/{chat_id}"
