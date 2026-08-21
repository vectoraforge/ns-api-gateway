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
`record_rejection`. The bounded reason lives only in telemetry and, for on-path routes, in the
audit row's `details.failure`. The client response names no issuer, no integration, and no failed
check -- and for §8.2 routes, which is every route this phase registers, no audit row is written.

**Entry to the audited path depends on one thing only**: whether the matched route+method carries
a non-`None` `operation` in its metadata. Never on how far the request got, never on which step
refused. All eight routes foundation registers declare `operation = None`, so no production request
in this phase writes a row; the registry is read from `scope["app"].state.route_registry` per
request precisely so a test can declare a route that does, and phases 37-45 supply the real ones.

The typed context travels on `scope["state"]`, which stays visible to the handler through
`request.state` and to the outer `RequestLoggingMiddleware` after `call_next`. Contextvars bound
below a `BaseHTTPMiddleware` never propagate back up, so binding identity to `structlog.contextvars`
and expecting the request log line to carry it would silently produce nothing (D-03 pins the stack).
"""
from datetime import UTC, datetime
from ipaddress import IPv6Address, ip_address
from uuid import UUID, uuid7

import structlog
from starlette.concurrency import run_in_threadpool
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

from nativespeaker.api.auth.audit import build_details
from nativespeaker.api.auth.context import (
    REQUEST_CONTEXT_SCOPE_KEY,
    ClientIpBucketKind,
    RequestContext,
)
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
            # No FULL match, Match.PARTIAL (wrong method) included. §4.1 places route/method
            # mismatch in the admission phase, so the router keeps its own 404 and its own 405
            # and no audit row is written.
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
                               bounded_reason=reason, meta=meta,
                               evaluated_at=evaluated_at, attempt_id=attempt_id)
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
                               bounded_reason=reason, meta=meta,
                               evaluated_at=evaluated_at, attempt_id=attempt_id)
            return

        # Step 4 -- resolution. Exactly one short session, closed before dispatch: no lock is held
        # and no network call is made while it is open.
        async with scope["app"].state.session_factory() as session:
            decision = await resolve_identity(session, issuer=claims.issuer,
                                              subject=claims.subject, meta=meta)

        # Step 5 -- the admission matrix.
        if isinstance(decision, Reject):
            # Every branch reachable here ran after verification, so the actor is known -- which is
            # the shape `audit.auth_events` requires for every result but `invalid_external_jwt`.
            await self._reject(scope, receive, send, error_class=decision.error_class,
                               result=decision.result, bounded_reason=None, meta=meta,
                               evaluated_at=evaluated_at, attempt_id=attempt_id,
                               actor_issuer=decision.actor_issuer,
                               actor_subject=decision.actor_subject)
            return

        # Step 6 -- attach and dispatch.
        scope.setdefault("state", {})[REQUEST_CONTEXT_SCOPE_KEY] = RequestContext(
            identity=decision.identity,
            route_metadata=meta,
            client_ip_bucket_kind=_bucket_kind(scope.get("client")),
            evaluated_at=evaluated_at,
            attempt_id=attempt_id,
        )
        await self.app(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send, *,
                      error_class: ErrorClass,
                      result: AuthEventResult,
                      bounded_reason: BoundedReason | None,
                      meta: RouteMetadata,
                      evaluated_at: datetime,
                      attempt_id: UUID,
                      actor_issuer: str | None = None,
                      actor_subject: str | None = None) -> None:
        """Record the rejection, then *return* the shared response -- never raise it (D-01).

        Telemetry fires for every rejection, on the audited path and off it. The audit row is
        written only when the matched route carries an operation, and is written **before** the
        response goes out -- `§4.1` is explicit that the row is not a side effect of the response
        having been sent.
        """
        record_rejection(scope["app"].state, result=result,
                         bounded_reason=bounded_reason, route=meta.path)
        if meta.operation is not None:
            await self._audit(scope, result=result, bounded_reason=bounded_reason, meta=meta,
                              evaluated_at=evaluated_at, attempt_id=attempt_id,
                              actor_issuer=actor_issuer, actor_subject=actor_subject)
        response = error_response(error_class)
        await response(scope, receive, send)

    async def _audit(self, scope: Scope, *,
                     result: AuthEventResult,
                     bounded_reason: BoundedReason | None,
                     meta: RouteMetadata,
                     evaluated_at: datetime,
                     attempt_id: UUID,
                     actor_issuer: str | None,
                     actor_subject: str | None) -> None:
        """Write the §4 row for an on-path rejection, standalone-durable (§4.1).

        Standalone because a barrier rejection happens before any consuming or mutating transaction
        exists; there is nothing to be atomic with. `actor_provider` is NULL on every branch that
        reaches here: `§4.2` permits it only from the stored `core.external_identities.provider`
        column of a resolved linked identity, and a rejection resolved none.

        Wrapped whole. `AuditWriter` already swallows a database failure, but a missing writer, an
        absent factory, or a caller-contract error would otherwise escape and turn a 401 into a
        500 -- telling the caller something the 401 does not, which is both an availability
        regression and an anti-oracle break.
        """
        try:
            await scope["app"].state.audit_writer.write_standalone(
                scope["app"].state.session_factory,
                operation=meta.operation,
                result=result,
                actor_issuer=actor_issuer,
                actor_subject=actor_subject,
                actor_provider=None,
                challenge_row_id=None,
                details=build_details(
                    context={"route": meta.path,
                             "method": scope["method"],
                             "operation": meta.operation,
                             "attempt_id": attempt_id,
                             "client_ip_bucket_kind": _bucket_kind(scope.get("client"))},
                    failure={"stage": "barrier",
                             "reason": None if bounded_reason is None else str(bounded_reason),
                             "retryable": False}),
                created_at=evaluated_at)
        except Exception:
            logger.exception("audit_write_skipped", result=str(result), route=meta.path)


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


def _bucket_kind(client) -> ClientIpBucketKind:
    """§4.4's bucket kind, from the gateway-resolved `scope["client"]` alone.

    Never recomputed from `X-Forwarded-For`, `Forwarded`, or any other client-supplied header, by
    this function or any later one. The address itself is not carried anywhere: §9 is deferred, so
    `xff_num_trusted_hops` is unpinned and an address would be trusted rather than proven (A3).
    """
    if not client:
        return ClientIpBucketKind.unresolved
    try:
        address = ip_address(client[0])
    except ValueError:
        return ClientIpBucketKind.unresolved
    return ClientIpBucketKind.ipv6 if isinstance(address, IPv6Address) else ClientIpBucketKind.ipv4
