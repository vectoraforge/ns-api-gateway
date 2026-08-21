"""D-03, D-04, Pitfall 6: the app-construction invariants the barrier depends on.

These are invisible at runtime except through absent log fields or an unauthenticated redirect,
which is why they get their own assertions against the real app.
"""
from nativespeaker.api.app.main import app as real_app

DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


class TestMiddlewareOrder:
    """D-03: RequestLoggingMiddleware outermost, the barrier directly beneath it."""

    def test_stack_is_logging_then_barrier_outermost_first(self):
        assert [m.cls.__name__ for m in real_app.user_middleware] == [
            "RequestLoggingMiddleware",
            "AuthBarrierMiddleware",
        ]

    def test_barrier_is_installed(self):
        """§2.3 condition 9 is structural: one middleware wraps the whole router."""
        assert "AuthBarrierMiddleware" in {m.cls.__name__ for m in real_app.user_middleware}


class TestDocumentationRoutes:
    """D-04: no unauthenticated schema dump, and no undeclared registered route."""

    def test_no_documentation_route_is_registered(self):
        registered_paths = {r.path for r in real_app.routes}
        assert registered_paths & DOC_PATHS == set()

    def test_openapi_is_still_generatable_as_a_method_call(self):
        """openapi_url=None removes the route, not the schema -- tests still introspect it."""
        assert "ErrorResponse" in real_app.openapi()["components"]["schemas"]


class TestRedirectSlashes:
    """Pitfall 6: a trailing-slash 307 is produced after the barrier already passed through."""

    def test_redirect_slashes_is_disabled(self):
        assert real_app.router.redirect_slashes is False
