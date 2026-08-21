"""The pre-handler auth barrier (§1.5) as a pure-ASGI middleware (D-01).

Deliberately not a `BaseHTTPMiddleware` subclass: `add_middleware` places user middleware outside
Starlette's `ExceptionMiddleware`, so `app.add_exception_handler` never sees what this class raises
and a raised registry error would surface as a 500. The reject path therefore *returns* the shared
error response -- it awaits the response object against `(scope, receive, send)` directly.
"""
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

from nativespeaker.api.auth.registry import Category, lookup
from nativespeaker.api.auth.wire import extract_bearer
from nativespeaker.api.errors import AUTH_REQUIRED, error_response


class AuthBarrierMiddleware:
    """Rejects an authenticated-category request that fails the §1.1 wire contract.

    This plan wires one path end to end: no identity resolution, no database read, no token
    verification. Plan 06 adds verification, resolution, the admission matrix, and the typed
    context on this same seam.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Capture NOTHING from app.state here. The middleware is constructed at add_middleware
        # time, before the lifespan runs, and the e2e rollback fixture works by swapping
        # app.state.session_factory afterwards -- anything cached here would write to the real
        # database and never roll back.

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # lifespan and websocket scopes pass straight through
            await self.app(scope, receive, send)
            return

        route = _match_full(scope)
        if route is None:
            # No FULL match, Match.PARTIAL (wrong method) included. §4.1 places route/method
            # mismatch in the admission phase, so the router keeps its own 404 and its own 405
            # and no audit row is written.
            await self.app(scope, receive, send)
            return

        metadata = lookup(scope["method"], route.path)
        # An undeclared route aborts boot via the §2.3 assertion, so `None` is unreachable in a
        # started process. It is still treated as authenticated here: a route carrying no
        # declaration gets the strictest treatment and must never silently become public.
        if metadata is not None and metadata.category is not Category.authenticated:
            await self.app(scope, receive, send)
            return

        _token, reason = extract_bearer(scope["headers"])  # plan 06 consumes the token
        if reason is not None:
            # Every bounded reason surfaces the identical status, body, and copy. The reason stays
            # internal -- audit `details.failure` and metric labels only (plan 03).
            response = error_response(AUTH_REQUIRED)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _match_full(scope: Scope):
    """Resolve the matched route by asking the router, taking the first `Match.FULL`.

    Starlette never sets `scope["route"]` on the way in -- FastAPI writes it inside
    `APIRoute.matches` during router dispatch, which happens after the barrier has already had to
    decide. Running the router's own matching code is the only way the barrier and the router can
    never disagree, which is the structural form of §2.3 condition 9.
    """
    for route in scope["app"].router.routes:
        match, _child_scope = route.matches(scope)
        if match == Match.FULL:
            return route
    return None
