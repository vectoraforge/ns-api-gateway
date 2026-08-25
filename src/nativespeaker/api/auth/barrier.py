"""The pre-handler auth barrier (§1.5) as a pure-ASGI middleware (D-01).

Deliberately not a `BaseHTTPMiddleware` subclass: `add_middleware` places user middleware outside
Starlette's `ExceptionMiddleware`, so `app.add_exception_handler` never sees what this class raises
and a raised registry error would surface as a 500. The reject path therefore *returns* the shared
error response -- it awaits the response object against `(scope, receive, send)` directly.

The six §1.5 steps run in order, per request:

1. read the route metadata -- available *before* dispatch, so a rejection can name the operation;
2. apply the §1.1 wire contract;
3. verify the token;
4. resolve `(issuer, subject)` in one query from one short session;
5. enforce the §1.3 admission matrix;
6. attach the §1.4 typed context and dispatch.

Every rejection at steps 2-5 returns the identical body its class declares and is recorded through
`record_rejection`, which is the only record a rejection leaves. The bounded reason lives in that
structured security log alone; the client response names no issuer, no integration, and no failed
check.

The typed context travels on `scope["state"]`, which stays visible to the handler through
`request.state` and to the outer `RequestLoggingMiddleware` after `call_next`. Contextvars bound
below a `BaseHTTPMiddleware` never propagate back up, so binding identity to `structlog.contextvars`
and expecting the request log line to carry it would silently produce nothing (D-03 pins the stack).
"""
from datetime import UTC, datetime
from uuid import uuid7

import structlog
from starlette.concurrency import run_in_threadpool
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

from nativespeaker.api.auth.context import REQUEST_CONTEXT_SCOPE_KEY, RequestContext
from nativespeaker.api.auth.identity import Reject, resolve_identity
from nativespeaker.api.auth.registry import Category, RouteMetadata, lookup
from nativespeaker.api.auth.telemetry import record_rejection
from nativespeaker.api.auth.wire import BoundedReason, extract_bearer
from nativespeaker.api.errors import AUTH_REQUIRED, ErrorClass, error_response
from nativespeaker.api.models.auth import AuthEventResult

logger = structlog.get_logger()


class AuthBarrierMiddleware:
    """The only place JWT acceptance and identity resolution happen.

    A handler consumes the context this attaches and nothing else. A route registered outside this
    middleware has no context, and the §1.4 accessors answer `auth_required` rather than handing
    back a `None` a handler could read as anonymous.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Capture nothing from the application here. This runs at `add_middleware` time, before
        # the lifespan, and the e2e rollback fixture swaps the session factory afterwards --
        # anything read now would write to the real database and never roll back. Everything the
        # request path needs is read per request, inside `__call__`.

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # lifespan and websocket scopes pass straight through
            await self.app(scope, receive, send)
            return

        route = _match_full(scope)
        if route is None:
            # No FULL match, Match.PARTIAL (wrong method) included. Route/method mismatch belongs
            # to the admission phase, so the router keeps its own 404 and its own 405.
            await self.app(scope, receive, send)
            return

        # Step 1 -- route metadata, read before dispatch. An undeclared route aborts boot via the
        # §2.3 assertion, so `None` is unreachable in a started process; it is answered with the
        # strictest disposition anyway, because a route carrying no declaration must never
        # silently become public. The registry comes off application state per request, like the
        # verifier and the session factory -- never captured in `__init__`.
        registry = scope["app"].state.route_registry
        meta = (lookup(scope["method"], route.path, registry)
                or _strictest(scope["method"], route.path))
        if meta.category is not Category.authenticated:
            await self.app(scope, receive, send)
            return

        # One evaluation time and one attempt id per request. Every time-dependent value derives
        # from this capture, so two reads within one request can never straddle a period boundary.
        evaluated_at = datetime.now(UTC)
        attempt_id = uuid7()

        # Step 2 -- the wire contract.
        token, reason = extract_bearer(scope["headers"])
        if token is None:
            await self._reject(scope, receive, send, error_class=AUTH_REQUIRED,
                               result=AuthEventResult.invalid_external_jwt,
                               bounded_reason=reason, meta=meta)
            return

        # Step 3 -- verification. `verify` returns rather than raises, for the same reason this
        # middleware returns rather than raises.
        #
        # Off the loop, always. `verify` is synchronous, and on a `kid` the cached JWKS set does not
        # match it performs a blocking `urlopen` inside PyJWT. Called directly from here that stalls
        # every other coroutine in the process -- including `/health/ready`, served by this same loop
        # -- for the length of one outbound round trip, at the choice of an unauthenticated caller
        # who has not yet proven anything. Envoy bounds how many such requests arrive; it cannot
        # un-block an event loop, and one request is enough. `run_in_threadpool` takes any
        # synchronous callable, so the `TokenVerifier` Protocol is unchanged and `verify` keeps
        # returning rather than raising (D-01).
        claims, reason = await run_in_threadpool(scope["app"].state.jwt_verifier.verify, token)
        if claims is None:
            await self._reject(scope, receive, send, error_class=AUTH_REQUIRED,
                               result=AuthEventResult.invalid_external_jwt,
                               bounded_reason=reason, meta=meta)
            return

        # Step 4 -- resolution. Exactly one short session, closed before dispatch: no lock is held
        # and no network call is made while it is open.
        async with scope["app"].state.session_factory() as session:
            decision = await resolve_identity(session, issuer=claims.issuer,
                                              subject=claims.subject,
                                              allow_preauth=meta.preauth_callable)

        # Step 5 -- the admission matrix.
        if isinstance(decision, Reject):
            await self._reject(scope, receive, send, error_class=decision.error_class,
                               result=decision.result, bounded_reason=None, meta=meta)
            return

        # Step 6 -- attach and dispatch.
        # `route.path` rather than `meta.path`: the two are equal by construction here, because the
        # metadata was looked up under the path of this very route object.
        scope.setdefault("state", {})[REQUEST_CONTEXT_SCOPE_KEY] = RequestContext(
            identity=decision.identity,
            route=route.path,
            evaluated_at=evaluated_at,
            attempt_id=attempt_id,
        )
        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, *,
                      error_class: ErrorClass,
                      result: AuthEventResult,
                      bounded_reason: BoundedReason | None,
                      meta: RouteMetadata) -> None:
        """Record the rejection, then *return* the shared response -- never raise it (D-01).

        Telemetry fires for every rejection, on every route. `record_rejection` carries the
        specific internal result and the bounded reason into the structured security log, and it is
        the only record a rejection leaves.
        """
        record_rejection(result=result, bounded_reason=bounded_reason, route=meta.path)
        response = error_response(error_class)
        await response(scope, receive, send)


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


def _strictest(method: str, path: str) -> RouteMetadata:
    """The disposition an undeclared route receives: authenticated, and nothing else granted."""
    return RouteMetadata(method=method, path=path, category=Category.authenticated)
