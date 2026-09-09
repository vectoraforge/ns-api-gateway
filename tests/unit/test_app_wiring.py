"""App-construction invariants admission depends on, asserted over the real app because runtime hides them."""
import pytest
from fastapi import Depends
from fastapi.routing import APIRoute

from nativespeaker.api.app.dependencies import (
    get_db,
    get_identity,
    get_linked_identity,
    verify_app_store_notification,
    verify_google_play_notification,
)
from nativespeaker.api.app.main import app as real_app

DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# Literals rather than derived from anything, so widening the exemption is a visible edit here.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user", "/auth/challenge"}
PROVIDER_CALLBACK_VERIFIERS = {"/webhooks/app-store": verify_app_store_notification,
                               "/webhooks/google-play/rtdn": verify_google_play_notification}
PROVIDER_CALLBACK_PATHS = set(PROVIDER_CALLBACK_VERIFIERS)


def _api_routes() -> list[APIRoute]:
    return [route for route in real_app.routes if isinstance(route, APIRoute)]


def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]


def _flattened(route: APIRoute) -> list:
    """Every dependency callable in resolution order, sub-dependencies depth-first under their parent."""
    order = []

    def walk(dependencies):
        for dependency in dependencies:
            order.append(dependency.call)
            walk(dependency.dependencies)

    walk(route.dependant.dependencies)
    return order


def _route_at(path: str) -> APIRoute:
    """The one registered route at this exact path."""
    routes = [route for route in _api_routes() if route.path == path]
    assert len(routes) == 1, f"{path} is registered {len(routes)} times"
    return routes[0]


class TestEveryRouteIsAuthenticated:
    """The structural replacement for the deleted startup assertion: the declaration is what serves traffic."""

    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   | PROVIDER_CALLBACK_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"

    def test_the_preauth_callable_route_still_resolves_the_identity(self):
        """Create-user is exempt from the narrowing, not from authentication: a linked caller is owed a 409."""
        for route in _api_routes():
            if route.path in PREAUTH_CALLABLE_PATHS:
                assert get_identity in _declared(route), route.path

    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant",
                                      "/auth/restore-subscription", "/auth/sign-out-all",
                                      "/users/me"))
    def test_a_narrowed_route_declares_the_linked_identity_narrowing(self, path):
        """Named rather than left to the generic case, which would also pass if the route were exempted."""
        declared = [_declared(route) for route in _api_routes() if route.path == path]
        assert declared, f"{path} is not a registered route"
        assert all(get_linked_identity in calls for calls in declared)

    @pytest.mark.parametrize("path", ("/auth/sync", "/auth/upgrade-anonymous",
                                      "/auth/claim-anonymous-grant",
                                      "/auth/claim-registered-grant",
                                      "/auth/restore-subscription", "/auth/sign-out-all",
                                      "/users/me"))
    def test_a_narrowed_route_is_in_neither_exemption_set(self, path):
        """The route is authenticated and narrowed, so widening either literal above would fail here."""
        assert path in {route.path for route in _api_routes()}
        assert path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS

    def test_the_public_allowlist_is_exactly_the_readiness_probe(self):
        """Read off the live router, not off the literal: a second open route fails here, not only below."""
        open_paths = {route.path for route in _api_routes()
                      if route.path not in PROVIDER_CALLBACK_PATHS
                      and get_linked_identity not in _declared(route)
                      and get_identity not in _declared(route)}
        assert open_paths == {"/health/ready"}

    def test_no_route_serves_without_an_identity_or_a_callback_declaration(self):
        """A second such route would have to be added to one of the two literals above to pass."""
        unauthenticated = {route.path for route in _api_routes()
                           if get_linked_identity not in _declared(route)
                           and get_identity not in _declared(route)}
        assert unauthenticated == PUBLIC_PATHS | PROVIDER_CALLBACK_PATHS

    def test_no_route_declares_a_wrapper_around_an_accessor(self):
        """The cache keys on the callable, so a `wraps` wrapper would key differently and verify twice."""
        for route in _api_routes():
            for call in _declared(route):
                wrapped = getattr(call, "__wrapped__", None)
                assert wrapped not in (get_linked_identity, get_identity), \
                    f"{route.path} declares a wrapper around {getattr(wrapped, '__name__', wrapped)}"


class TestTheSignOutRouteOpensNoSession:
    """D-04. The revocation writes no row and reads no table, so the handler declares no session."""

    def test_sign_out_all_declares_no_database_session(self):
        # `_flattened` walks sub-dependencies, so a session taken through a service is visible here.
        assert get_db not in _flattened(_route_at("/auth/sign-out-all"))


class TestTheProviderCallbackPartition:
    """Membership is the set of routes on the webhooks router, counted here against one literal."""

    def test_the_partition_is_exactly_the_routes_on_the_webhooks_router(self):
        from nativespeaker.api.routers import webhooks_router

        assert {route.path for route in webhooks_router.routes} == PROVIDER_CALLBACK_PATHS

    @pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
    def test_each_callback_route_declares_its_own_verifier_and_neither_identity(self, path, verifier):
        """Its own, not any: one route declaring the other's verifier would pass a shared-name case."""
        calls = _declared(_route_at(path))
        assert verifier in calls
        assert get_identity not in calls
        assert get_linked_identity not in calls

    @pytest.mark.parametrize("verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.values(),
                                                key=lambda call: call.__name__))
    def test_no_route_outside_the_partition_declares_any_callback_verifier(self, verifier):
        leaked = [route.path for route in _api_routes()
                  if route.path not in PROVIDER_CALLBACK_PATHS
                  and verifier in _declared(route)]
        assert leaked == [], f"routes declaring a callback verifier off the partition: {leaked}"

    @pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
    def test_the_verifier_is_the_routes_first_declared_dependency(self, path, verifier):
        """D-02. A reordered parameter list is what this catches, and it costs a connection per junk request."""
        assert _route_at(path).dependant.dependencies[0].call is verifier

    @pytest.mark.parametrize("path,verifier", sorted(PROVIDER_CALLBACK_VERIFIERS.items()))
    def test_the_verifier_resolves_before_any_session_is_taken(self, path, verifier):
        """D-02. `get_db` is a sub-dependency, so the order is read off the flattened resolution walk."""
        order = _flattened(_route_at(path))
        assert order.index(verifier) < order.index(get_db)

    def test_the_partition_is_disjoint_from_both_other_literals(self):
        """A callback path in either exemption set would make the three literals disagree silently."""
        assert PROVIDER_CALLBACK_PATHS & (PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS) == set()


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
        from nativespeaker.api.schemas.auth import Identity, LinkedIdentity
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
                           who: LinkedIdentity = Depends(get_linked_identity),
                           admitted: Identity = Depends(get_identity)):
            # `get_linked_identity` narrows rather than passes through, so the two are not one
            # object; sharing both resolved rows is what says the resolution happened once.
            same = who.user is admitted.user and who.identity is admitted.identity
            return {"same": same, "user": str(who.user.id)}

        app.include_router(router)
        app.state.jwt_verifier = _CountingVerifier()
        app.state.session_factory = _Session

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/chats/0199a0d0-0000-7000-8000-000000000000",
                              headers={"Authorization": f"Bearer {make_token(sub=subject)}"})

        assert response.status_code == 200, response.json()
        assert counts["verify"] == 1, f"the JWT was verified {counts['verify']} times"
        assert counts["query"] == 1, f"identity was resolved {counts['query']} times"
        # Both declarations were served by the one cached resolution, not by two equal ones.
        assert response.json()["same"] is True
