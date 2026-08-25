"""D-04, Pitfall 6 and 37.1 D-07: the app-construction invariants admission depends on.

These are invisible at runtime except through an unauthenticated schema dump, an unauthenticated
redirect, or a route that quietly serves without a token -- which is why they get their own
assertions against the real app.

`TestEveryRouteIsAuthenticated` is the **structural replacement for the startup route-enumeration
assertion 37.1 D-06 deleted**. That assertion's first two conditions were set equality between the
router and a parallel table of auth declarations, and the whole failure class they guarded was the
table drifting from what actually serves traffic. There is no table now: the declaration IS what
serves traffic, so the property is asserted directly over the live router and can no longer
disagree with itself. What it still catches is the case that mattered -- a route added later
without an auth declaration.
"""
from fastapi import Depends
from fastapi.routing import APIRoute

from nativespeaker.api.app.dependencies import get_linked_identity, get_request_context
from nativespeaker.api.app.main import app as real_app

DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}

# The whole §2.1 public allowlist, and the one route an unlinked caller may reach. Every other
# route on the app must carry `get_linked_identity`. Written as literals rather than derived from
# anything, so widening the exemption is a visible edit to this line.
PUBLIC_PATHS = {"/health/ready"}
PREAUTH_CALLABLE_PATHS = {"/auth/create-user"}


def _api_routes() -> list[APIRoute]:
    return [route for route in real_app.routes if isinstance(route, APIRoute)]


def _declared(route: APIRoute) -> list:
    """The callables FastAPI resolved for this route, router-level declarations included."""
    return [dependency.call for dependency in route.dependant.dependencies]


class TestEveryRouteIsAuthenticated:
    """T-37.1-01 / T-37.1-02: no route serves traffic without an auth declaration."""

    def test_every_route_but_the_two_exemptions_requires_a_linked_identity(self):
        missing = [route.path for route in _api_routes()
                   if route.path not in PUBLIC_PATHS | PREAUTH_CALLABLE_PATHS
                   and get_linked_identity not in _declared(route)]
        assert missing == [], f"routes serving without a linked-identity declaration: {missing}"

    def test_the_preauth_callable_route_still_resolves_the_context(self):
        """`POST /auth/create-user` is exempt from the narrowing, not from authentication.

        It declares `get_request_context`, so the token is still verified and the identity still
        resolved before its handler runs -- what it does not do is 401 a linked caller, because
        §02 prepare step 1 owes that caller a 409 instead.
        """
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
        """D-07's caching contract: FastAPI keys the per-request cache on the callable object.

        A `functools.wraps` wrapper would key differently at each level and run the JWT verify and
        the identity query a second time. This catches the `wraps` form, which is the one that
        looks harmless in review because the wrapper reports the accessor's own name.
        `TestTheAuthDependencyIsResolvedOncePerRequest` below is the general proof: it counts, so
        no wrapper of any shape gets past it.
        """
        for route in _api_routes():
            for call in _declared(route):
                wrapped = getattr(call, "__wrapped__", None)
                assert wrapped not in (get_linked_identity, get_request_context), \
                    f"{route.path} declares a wrapper around {getattr(wrapped, '__name__', wrapped)}"


class TestDocumentationRoutes:
    """D-04: no unauthenticated schema dump.

    Stronger under D-07, not weaker: FastAPI registers these four on `app.router` directly, so they
    belong to no `APIRouter` and would carry no router-level dependency at all.
    """

    def test_no_documentation_route_is_registered(self):
        registered_paths = {r.path for r in real_app.routes}
        assert registered_paths & DOC_PATHS == set()

    def test_openapi_is_still_generatable_as_a_method_call(self):
        """openapi_url=None removes the route, not the schema -- tests still introspect it."""
        assert "ErrorResponse" in real_app.openapi()["components"]["schemas"]


class TestRedirectSlashes:
    """Pitfall 6: the trailing-slash 307 is produced before any route's dependencies run."""

    def test_redirect_slashes_is_disabled(self):
        assert real_app.router.redirect_slashes is False


class TestTheAuthDependencyIsResolvedOncePerRequest:
    """T-37.1-11, measured: one verify and one identity query, across both declaration levels.

    Nothing else proves this. The counting harness lives in `test_identity_accessors.py`, which
    counts sessions; this case counts the verify itself, on a route declaring `get_linked_identity`
    at both levels *and* `get_request_context` beneath it -- the exact shape every `/chats` route
    has through `get_chat_service`, and the shape that ran everything twice until the narrowing
    accessors took the context as a parameter instead of calling it.
    """

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
